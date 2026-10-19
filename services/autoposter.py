"""Автоматическая публикация объявлений в Telegram-канал."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select

from config import settings
from database import Property, async_session_factory


logger = logging.getLogger(__name__)


async def get_next_property() -> Property | None:
    """Выбрать активный объект, не публиковавшийся последние три дня."""
    async with async_session_factory() as session:
        stmt = (
            select(Property)
            .where(Property.status == "active")
            .where(
                or_(
                    Property.last_posted_at.is_(None),
                    Property.last_posted_at < datetime.utcnow() - timedelta(days=3),
                )
            )
            .order_by(Property.last_posted_at.asc().nullsfirst())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


def format_post(prop: Property) -> tuple[str, InlineKeyboardMarkup | None]:
    """Сформировать HTML-текст публикации и кнопку бота."""
    lines = [f"🏠 <b>{prop.title}</b>"]
    if prop.price:
        lines.append(f"💰 {prop.price:,} ₽".replace(",", " "))
    if prop.address:
        lines.append(f"📍 {prop.address}")
    if prop.rooms:
        lines.append(f"🚪 Комнат: {prop.rooms}")
    if prop.area:
        lines.append(f"📐 Площадь: {prop.area} м²")
    if prop.floor:
        lines.append(f"🏢 Этаж: {prop.floor}")
    lines.extend(("", "Подробнее в боте: @MyReeltor_bot"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🔍 Найти похожие",
        url=f"https://t.me/MyReeltor_bot?start=property_{prop.id}",
    )]])
    return "\n".join(lines), keyboard


async def post_random_property(bot: Bot) -> bool:
    """Опубликовать следующий подходящий объект в канал."""
    prop = await get_next_property()
    if prop is None:
        logger.info("Автопостер: нет объектов для публикации")
        return False
    text, keyboard = format_post(prop)
    try:
        if prop.photo_url:
            await bot.send_photo(chat_id=settings.channel_id, photo=prop.photo_url, caption=text,
                                 parse_mode="HTML", reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=settings.channel_id, text=text,
                                   parse_mode="HTML", reply_markup=keyboard)
        async with async_session_factory() as session:
            result = await session.execute(select(Property).where(Property.id == prop.id))
            current = result.scalar_one_or_none()
            if current:
                current.last_posted_at = datetime.utcnow()
                await session.commit()
        logger.info("Автопостер: опубликован объект #%s в канал", prop.id)
        return True
    except Exception:
        logger.exception("Автопостер: ошибка публикации объекта #%s", prop.id)
        return False
