
"""Точка входа Telegram-бота."""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher

from config import settings
from database import init_db
from handlers.admin import router as admin_router
from handlers.payment import router as payment_router
from handlers.search import router as search_router
from handlers.start import router as start_router


bot = Bot(token=settings.bot_token)


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
    # Используем maxBytes (camelCase) — совместимо с Python 3.11 и ниже
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


async def main() -> None:
    """Инициализировать БД и запустить polling."""
    configure_logging()
    logger = logging.getLogger(__name__)
    dispatcher = Dispatcher()

    # Порядок: сначала команды и callback'и, потом текстовый поиск
    dispatcher.include_router(payment_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(start_router)
    dispatcher.include_router(search_router)

    try:
        await init_db()
        logger.info("База данных инициализирована")
        await dispatcher.start_polling(bot)
    except Exception:
        logger.exception("Не удалось инициализировать базу данных или запустить бота")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())