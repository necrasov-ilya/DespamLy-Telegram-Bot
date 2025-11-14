"""
Регистрация всех handlers в приложении.
Порядок важен: специфичные handlers должны быть перед общими.
"""
from __future__ import annotations

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .setup import (
    on_my_chat_member,
    on_activate_initial_callback,
    on_restore_config_callback,
    on_reset_config_callback,
)
from .moderation import on_message
from .owner_menu import (
    cmd_mychats,
    on_chat_menu_callback,
    on_activate_callback,
    on_pause_callback,
    on_change_mode_callback,
    on_set_mode_callback,
    on_back_to_mychats_callback,
    on_help_callback,
)
from .owner_actions import (
    on_ban_callback,
    on_ham_callback,
    on_whitelist_callback,
    on_whitelist_menu_callback,
    on_clear_whitelist_callback,
    on_stats_callback,
    on_delete_chat_callback,
    on_confirm_delete_callback,
    on_setup_moderator_callback,
)
from .chat_commands import cmd_status, cmd_pause, cmd_resume, cmd_test, cmd_link_moderator
from .info_commands import cmd_start, cmd_primer, cmd_help

from utils.logger import get_logger

LOGGER = get_logger(__name__)


def register_handlers(app: Application) -> None:
    """
    Регистрирует все handlers в приложении.
    
    Порядок регистрации:
    1. ChatMemberHandler (on_my_chat_member) - для отслеживания добавления/удаления бота
    2. CommandHandlers - команды
    3. CallbackQueryHandlers - обработка callbacks (от специфичных к общим)
    4. MessageHandler - обработка всех текстовых сообщений (самый последний)
    """
    
    # 1. Chat member updates (добавление/удаление бота)
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    LOGGER.info("Registered: ChatMemberHandler (setup)")
    
    # 2. Commands
    # Info commands (работают везде)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("primer", cmd_primer))
    app.add_handler(CommandHandler("help", cmd_help))
    
    # Owner commands (работают в ЛС)
    app.add_handler(CommandHandler("mychats", cmd_mychats))
    
    # Chat commands (работают в группах)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("link_moderator", cmd_link_moderator))
    
    LOGGER.info("Registered: CommandHandlers")
    
    # 3. Callback handlers (от специфичных к общим)
    
    # Setup callbacks
    app.add_handler(CallbackQueryHandler(on_activate_initial_callback, pattern=r"^activate_initial:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_restore_config_callback, pattern=r"^restore_config:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_reset_config_callback, pattern=r"^reset_config:-?\d+$"))
    
    # Owner menu callbacks
    app.add_handler(CallbackQueryHandler(on_chat_menu_callback, pattern=r"^chat_menu:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_activate_callback, pattern=r"^activate:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_pause_callback, pattern=r"^pause:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_change_mode_callback, pattern=r"^change_mode:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_set_mode_callback, pattern=r"^set_mode:-?\d+:\w+$"))
    app.add_handler(CallbackQueryHandler(on_back_to_mychats_callback, pattern=r"^back_to_mychats$"))
    app.add_handler(CallbackQueryHandler(on_help_callback, pattern=r"^help_mychats$"))
    
    # Owner action callbacks (из уведомлений)
    app.add_handler(CallbackQueryHandler(on_ban_callback, pattern=r"^ban:-?\d+:-?\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(on_ham_callback, pattern=r"^ham:-?\d+:-?\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(on_whitelist_callback, pattern=r"^whitelist:-?\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(on_whitelist_menu_callback, pattern=r"^whitelist_menu:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_clear_whitelist_callback, pattern=r"^clear_whitelist:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_stats_callback, pattern=r"^stats:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_delete_chat_callback, pattern=r"^delete_chat:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_confirm_delete_callback, pattern=r"^confirm_delete:-?\d+$"))
    app.add_handler(CallbackQueryHandler(on_setup_moderator_callback, pattern=r"^setup_moderator:-?\d+$"))
    
    LOGGER.info("Registered: CallbackQueryHandlers")
    
    # 4. Message handler (должен быть последним - ловит все текстовые сообщения)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_message
        )
    )
    LOGGER.info("Registered: MessageHandler (moderation)")
    
    LOGGER.info("All handlers registered successfully")


__all__ = ["register_handlers"]
