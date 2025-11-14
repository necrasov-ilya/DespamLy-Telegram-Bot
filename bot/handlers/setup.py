"""Automatic chat registration when bot is added."""
from __future__ import annotations

from telegram import Update
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
    
    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER) and \
       old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        
        LOGGER.info(
            f"Bot added to chat {chat.id} ({chat.title}) by user {owner_id}"
        )
        
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
            
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 <b>Привет! Я DespamLy</b> — бот для защиты от спама.\n\n"
                    "Я автоматически обнаруживаю и удаляю спам с помощью ML-моделей.\n\n"
                    "<b>Быстрый старт:</b>\n"
                    "1️⃣ Используй /mychats для настройки\n"
                    "2️⃣ Активируй защиту\n"
                    "3️⃣ Настрой модераторский канал (опционально)\n\n"
                    "📖 Подробнее: /primer"
                ),
                parse_mode=ParseMode.HTML
            )
            
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
    
    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and \
         old_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        
        LOGGER.info(f"Bot removed from chat {chat.id} ({chat.title})")
        
        try:
            storage.chat_configs.update(chat.id, is_active=False)
            LOGGER.info(f"Chat {chat.id} deactivated")
        except Exception as e:
            LOGGER.error(f"Failed to deactivate chat {chat.id}: {e}")
