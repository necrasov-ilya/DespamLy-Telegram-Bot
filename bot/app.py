from __future__ import annotations

from typing import List

from telegram import BotCommand
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, Defaults

from config.config import settings
from utils.logger import get_logger
from bot.handlers import register_handlers
from storage.bootstrap import init_storage

LOGGER = get_logger(__name__)

BOT_COMMANDS: List[BotCommand] = [
    # Команды для владельцев (в ЛС)
    BotCommand("mychats", "Управление чатами"),
    
    # Команды для групп
    BotCommand("status", "Статус защиты чата"),
    BotCommand("pause", "Приостановить защиту"),
    BotCommand("resume", "Возобновить защиту"),
]


def run_polling() -> None:
    LOGGER.info("▶️  Запуск бота (polling)…")
    
    init_storage()
    
    app = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .build()
    )

    register_handlers(app)

    async def post_init(application: Application) -> None:
        """Выполняется после инициализации приложения"""
        if BOT_COMMANDS:
            await application.bot.set_my_commands(BOT_COMMANDS)
        LOGGER.info("Application готово.")

    app.post_init = post_init

    LOGGER.info("Запуск polling...")
    # ВАЖНО: my_chat_member нужен для ChatMemberHandler (автодобавление в чаты)
    app.run_polling(
        allowed_updates=["message", "callback_query", "my_chat_member"],
    )
    LOGGER.info("Бот завершил работу.")


if __name__ == "__main__":
    run_polling()
