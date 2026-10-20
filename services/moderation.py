"""Автоматическая модерация пользовательских заявок."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import settings
from database import Property, UserListing, add_property, async_session_factory


logger = logging.getLogger(__name__)
SPAM_PATTERN = re.compile(r"https?://|www\.|casino|казино|мат", re.IGNORECASE)


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_{id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_{id}"),
    ]])


async def _get_listing(listing_id: int) -> UserListing | None:
    async with async_session_factory() as session:
        result = await session.execute(select(UserListing).where(UserListing.id == listing_id))
        return result.scalar_one_or_none()


async def publish_listing(listing_id: int, bot: Bot) -> bool:
    """Одобрить, создать Property и опубликовать заявку в канале."""
    listing = await _get_listing(listing_id)
    if listing is None:
        return False
    property_id = await add_property(
        title=listing.title or "Заявка",
        price=listing.price,
        address=listing.address,
        district=listing.district,
        rooms=listing.rooms,
        area=listing.area,
        description=listing.description,
        seller_telegram=listing.contact,
        source="user_listing",
        source_url=None,
    )
    text = f"🏠 <b>{listing.title or 'Заявка'}</b>\n"
    if listing.price:
        text += f"💰 {listing.price:,} ₽\n".replace(",", " ")
    if listing.address or listing.district:
        text += f"📍 {listing.address or listing.district}\n"
    if listing.rooms:
        text += f"🚪 Комнат: {listing.rooms}\n"
    if listing.area:
        text += f"📐 Площадь: {listing.area} м²\n"
    if listing.description:
        text += f"\n{listing.description}\n"
    text += "\n💬 Для связи: " + (listing.contact or "через бота")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Подать объявление", url="https://t.me/MyReeltor_bot?start=sell"),
        InlineKeyboardButton(text="👀 Ищу", url="https://t.me/MyReeltor_bot?start=buy"),
    ]])
    if listing.type == "sell":
        sent = await bot.send_message(settings.channel_id, text, parse_mode="HTML", reply_markup=keyboard)
        message_id = sent.message_id
    else:
        message_id = None
    async with async_session_factory() as session:
        current = await session.get(UserListing, listing_id)
        if current:
            current.status = "approved"
            current.message_id = message_id
            await session.commit()
    logger.info("Заявка #%s опубликована, объект #%s", listing_id, property_id)
    return True


async def auto_moderate(listing_id: int, bot: Bot) -> None:
    """Автоматически одобрить чистую заявку или отправить её админу."""
    listing = await _get_listing(listing_id)
    if listing is None:
        return
    reasons = []
    if listing.type == "sell" and not listing.title:
        reasons.append("нет названия")
    if listing.type == "sell" and not listing.price:
        reasons.append("нет цены")
    if not listing.contact:
        reasons.append("нет контакта")
    combined = " ".join(filter(None, [listing.title, listing.description, listing.address, listing.contact]))
    if SPAM_PATTERN.search(combined):
        reasons.append("подозрительный текст")
    async with async_session_factory() as session:
        duplicate = await session.execute(select(UserListing).where(
            UserListing.id != listing_id,
            UserListing.title == listing.title,
            UserListing.price == listing.price,
            UserListing.status.in_(["approved", "pending_review"]),
        ).limit(1))
        if duplicate.scalar_one_or_none() is not None:
            reasons.append("дубликат")
    if not reasons:
        await publish_listing(listing_id, bot)
        return
    async with async_session_factory() as session:
        current = await session.get(UserListing, listing_id)
        if current:
            current.status = "pending_review"
            await session.commit()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{listing_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{listing_id}"),
    ]])
    await bot.send_message(settings.admin_id, f"⚠️ Заявка #{listing_id} требует проверки. Причины: {', '.join(reasons)}", reply_markup=keyboard)
