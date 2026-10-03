"""Обработчик текстовых запросов на поиск недвижимости."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from database import Property, async_session_factory, get_or_create_user, update_trial_used
from services.access import (
    get_access_level,
    get_limit_for_level,
    LEVEL_BLOCKED,
    LEVEL_CHANNEL,
    LEVEL_PAID,
    LEVEL_TRIAL,
)


router = Router()
logger = logging.getLogger(__name__)


def paywall_keyboard() -> InlineKeyboardMarkup:
    """Кнопка «Оформить подписку»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Оформить подписку", callback_data="buy_subscription")],
        ]
    )


def format_property(prop: Property) -> str:
    """Собрать карточку объекта для отправки."""
    lines = [f"🏠 <b>{prop.title}</b>"]
    if prop.price:
        lines.append(f"💰 {prop.price:,} ₽".replace(",", " "))
    if prop.address:
        lines.append(f"📍 {prop.address}")
    if prop.rooms:
        lines.append(f"🚪 Комнат: {prop.rooms}")
    if prop.area:
        lines.append(f"📐 Площадь: {prop.area} м²")
    if prop.description:
        lines.append(f"\n{prop.description[:300]}")
    return "\n".join(lines)


async def fetch_properties(limit: int | None) -> list[Property]:
    """Взять первые N объектов из базы. Пока без парсинга запроса."""
    async with async_session_factory() as session:
        stmt = select(Property)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


@router.message(lambda msg: msg.text is not None and not msg.text.startswith("/"))
async def search_handler(message: Message) -> None:
    """Обработать текстовый запрос на поиск."""
    if message.from_user is None or message.text is None:
        return

    try:
        user = await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        level = await get_access_level(message.bot, user)
        logger.info("Запрос от %s, уровень: %s", message.from_user.id, level)

        # Заблокирован — показываем пейволл
        if level == LEVEL_BLOCKED:
            await message.answer(
                "🔒 Бесплатный запрос использован.\n\n"
                "Оформи подписку — и ищи без ограничений на 30 дней.",
                reply_markup=paywall_keyboard(),
            )
            return

        # Определяем лимит
        limit = get_limit_for_level(level)

        # Ищем объекты
        properties = await fetch_properties(limit)

        if not properties:
            await message.answer(
                "Пока нет подходящих объектов. Попробуй позже или измени параметры."
            )
            return

        # Отправляем карточки
        for prop in properties:
            await message.answer(format_property(prop))

        # Сжигаем триал (для trial и channel)
        if level in (LEVEL_TRIAL, LEVEL_CHANNEL):
            await update_trial_used(message.from_user.id)
            await message.answer(
                f"🎁 Это был твой бесплатный запрос ({len(properties)} объектов).\n\n"
                "Чтобы искать без ограничений — оформи подписку.",
                reply_markup=paywall_keyboard(),
            )
        elif level == LEVEL_PAID:
            await message.answer(
                f"Найдено объектов: {len(properties)}. Подписка активна — можешь искать дальше."
            )

    except Exception:
        logger.exception("Ошибка при обработке поискового запроса")
        await message.answer("Сервис временно недоступен, попробуйте позже.")