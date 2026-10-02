"""Обработчик команды /start."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from database import User, async_session_factory


router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Создать пользователя при первом обращении и поприветствовать его."""
    if message.from_user is None:
        return

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                )
                session.add(user)
                await session.commit()
                logger.info("Создан пользователь Telegram")
            await message.answer(
                "Добро пожаловать! Напишите параметры недвижимости, и я помогу с поиском."
            )
    except Exception:
        logger.exception("Не удалось обработать команду /start")
        await message.answer("Сервис временно недоступен, попробуйте позже.")
