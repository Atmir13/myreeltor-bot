
"""Обработчик команды /start."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import settings
from database import get_or_create_user
from services.access import check_channel_subscription


router = Router()
logger = logging.getLogger(__name__)


def subscribe_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Подписаться на канал»."""
    channel = settings.channel_id or ""
    channel_username = channel.lstrip("@")
    url = f"https://t.me/{channel_username}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=url)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")],
        ]
    )


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Создать пользователя при первом обращении и поприветствовать его."""
    if message.from_user is None:
        return

    try:
        user = await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        is_subscribed = await check_channel_subscription(message.bot, message.from_user.id)

        if is_subscribed:
            await message.answer(
                "Привет! Это твой Реелтор — помогу найти квартиру или дом.\n\n"
                "Ты подписан на наш канал — тебе доступно <b>5 объектов</b> в первом запросе.\n\n"
                "Напиши, что ищешь. Например:\n"
                "— двушка до 15 млн\n"
                "— дом 4 комнаты до 20 млн",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "Привет! Это твой Реелтор — помогу найти квартиру или дом.\n\n"
                "🎁 <b>Подпишись на наш канал</b> — и получишь <b>5 объектов</b> вместо 2 в первом запросе.\n\n"
                "Напиши, что ищешь. Например:\n"
                "— двушка до 15 млн\n"
                "— дом 4 комнаты до 20 млн",
                reply_markup=subscribe_keyboard(),
                parse_mode="HTML",
            )

    except Exception:
        logger.exception("Не удалось обработать команду /start")
        await message.answer("Сервис временно недоступен, попробуйте позже.")


@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery) -> None:
    """Проверить подписку после нажатия кнопки «Я подписался»."""
    if callback.from_user is None or callback.message is None:
        return

    is_subscribed = await check_channel_subscription(callback.bot, callback.from_user.id)

    if is_subscribed:
        await callback.message.edit_text(
            "✅ Отлично!\n\n"
            "Ты подписан на канал — тебе доступно <b>5 объектов</b> в первом запросе.\n\n"
            "Напиши, что ищешь. Например:\n"
            "— двушка до 15 млн\n"
            "— дом 4 комнаты до 20 млн",
            parse_mode="HTML",
        )
        await callback.answer("Подписка подтверждена!")
    else:
        await callback.answer(
            "Ты ещё не подписан на канал. Подпишись и нажми кнопку снова.",
            show_alert=True,
        )