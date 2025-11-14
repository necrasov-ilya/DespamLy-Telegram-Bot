"""
Автоматическая регистрация чатов при добавлении бота.
Обрабатывает событие on_my_chat_member.
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes

from storage import get_storage, ChatConfigInput
from utils.logger import get_logger

LOGGER = get_logger(__name__)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка добавления/удаления бота из чата.
    При добавлении: создаёт chat_config с is_active=False.
    При удалении: деактивирует chat_config.
    """
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
    
    # Бота добавили в чат (стал администратором или участником)
    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER) and \
       old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        
        LOGGER.info(
            f"Bot added to chat {chat.id} ({chat.title}) by user {owner_id}"
        )
        
        # Создаём конфигурацию чата (не активна по умолчанию)
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
            
            # Отправляем приветствие в чат
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 Привет! Я DespamLy - бот для защиты от спама.\n\n"
                    "Чтобы активировать защиту, настрой меня в личных сообщениях:\n"
                    "Напиши мне /mychats"
                ),
                parse_mode=ParseMode.HTML
            )
            
            # Отправляем уведомление владельцу в ЛС
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"✅ Бот добавлен в чат <b>{chat.title}</b>\n\n"
                        f"Чтобы настроить защиту от спама, используй команду /mychats"
                    ),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                LOGGER.warning(f"Failed to send DM to owner {owner_id}: {e}")
                
        except Exception as e:
            LOGGER.error(f"Failed to create chat config for {chat.id}: {e}")
    
    # Бота удалили из чата
    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and \
         old_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        
        LOGGER.info(f"Bot removed from chat {chat.id} ({chat.title})")
        
        try:
            # Деактивируем чат вместо удаления (сохраняем статистику)
            storage.chat_configs.update(chat.id, is_active=False)
            LOGGER.info(f"Chat {chat.id} deactivated")
        except Exception as e:
            LOGGER.error(f"Failed to deactivate chat {chat.id}: {e}")
