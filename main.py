"""Точка входа Telegram-бота и сайта-каталога."""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat

from config import settings
from database import init_db
from handlers.admin import router as admin_router
from handlers.payment import router as payment_router
from handlers.forms import router as forms_router
from handlers.search import router as search_router
from handlers.start import router as start_router
from web.app import app as fastapi_app
from services.scheduler import start_scheduler


bot = Bot(token=settings.bot_token)
dp = Dispatcher()
dp.include_router(payment_router)
dp.include_router(forms_router)
dp.include_router(admin_router)
dp.include_router(start_router)
dp.include_router(search_router)


async def setup_commands(bot: Bot) -> None:
    """Настроить меню команд для админа и пользователей."""
    user_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Помощь"),
    ]
    admin_commands = user_commands + [
        BotCommand(command="moderation", description="Управление объявлениями"),
        BotCommand(command="pending", description="Заявки на проверку"),
        BotCommand(command="sync_ads", description="Синхронизация с API"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="grant", description="Выдать подписку"),
        BotCommand(command="revoke", description="Отозвать подписку"),
        BotCommand(command="check", description="Статус пользователя"),
    ]
    await bot.set_my_commands(user_commands)
    await bot.set_my_commands(commands=admin_commands, scope=BotCommandScopeChat(chat_id=settings.admin_id))


def configure_logging() -> None:
    """Настроить вывод логов в консоль и logs/bot.log."""
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


async def run_bot() -> None:
    """Запустить Telegram polling."""
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


async def run_site() -> None:
    """Запустить FastAPI-сайт на порту Amvera."""
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    """Инициализировать базу и параллельно запустить бота и сайт."""
    configure_logging()
    logger = logging.getLogger(__name__)
    try:
        await init_db()
        await setup_commands(bot)
        logger.info("База данных и меню команд инициализированы")
        scheduler = start_scheduler(bot)
        try:
            await asyncio.gather(run_bot(), run_site())
        finally:
            scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("Не удалось запустить бота или сайт")


if __name__ == "__main__":
    asyncio.run(main())
