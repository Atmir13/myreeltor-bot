
"""Обработчик команды /start."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import settings
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import (
    ChatAgreement, async_session_factory, get_or_create_user, get_pending_grant,
    delete_pending_grant, update_subscription,
)
from services.access import check_channel_subscription
from handlers.forms import BuyForm, SellForm


router = Router()
logger = logging.getLogger(__name__)

RULES_TEXT = (
    "📜 <b>ПРАВИЛА КАНАЛА</b>\n"
    "1. Все объявления размещаются через бота @MyReeltor_bot.\n"
    "2. Администрация канала не является стороной сделки и не несёт ответственности "
    "за достоверность информации, качество объектов и действия участников.\n"
    "3. Все переговоры, проверка документов и расчёты — личная ответственность покупателя и продавца.\n"
    "4. Размещая объявление, пользователь подтверждает, что имеет право на его публикацию.\n\n"
    "⚠️ <b>ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ</b>\n"
    "Администрация канала не несёт ответственности за любые убытки, возникшие "
    "в результате использования информации из канала."
)


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
async def start_handler(message: Message, state: FSMContext) -> None:
    """Создать пользователя при первом обращении и поприветствовать его."""
    if message.from_user is None:
        return

    try:
        payload = (message.text or "").split(maxsplit=1)[1].strip() if " " in (message.text or "") else ""
        if payload.startswith("grant_"):
            token = payload.removeprefix("grant_")
            pending = await get_pending_grant(token)
            if pending is None:
                await message.answer("Ссылка недействительна.")
                return
            user = await get_or_create_user(message.from_user.id, message.from_user.username)
            expires_at = await update_subscription(message.from_user.id, 30, "grant_link", 0)
            await delete_pending_grant(token)
            await message.answer("🎉 Вам выдана подписка на 30 дней! Приятного поиска.")
            await message.bot.send_message(settings.admin_id, f"✅ Пользователь @{message.from_user.username or pending.username} активировал подписку по ссылке.")
            return
        if payload == "subscribe":
            await state.clear()
            await message.answer(
                RULES_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="✅ Я согласен и подписаться",
                        callback_data="subscribe_confirm",
                    ),
                ]]),
            )
            return
        if payload == "sell":
            await state.set_state(SellForm.waiting_title)
            await message.answer("🏠 Подайте объявление. Укажите название объекта:")
            return
        if payload == "buy":
            await state.set_state(BuyForm.waiting_type)
            await message.answer("👀 Что вы ищете? Укажите тип недвижимости:")
            return
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


@router.callback_query(F.data == "subscribe_confirm")
async def subscribe_confirm_callback(callback: CallbackQuery) -> None:
    """Проверить подписку и сохранить явно данное согласие с правилами."""
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    try:
        if not await check_channel_subscription(callback.bot, callback.from_user.id):
            await callback.message.answer(
                "Ты ещё не подписан на канал. Подпишись и нажми кнопку снова.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="📢 Подписаться на канал", url="https://t.me/MyReeltor1",
                    ),
                ]]),
            )
            return
        async with async_session_factory() as session:
            agreement = await session.scalar(
                select(ChatAgreement).where(ChatAgreement.telegram_id == callback.from_user.id)
            )
            if agreement is None:
                session.add(ChatAgreement(telegram_id=callback.from_user.id))
                try:
                    await session.commit()
                except IntegrityError:
                    # Два одновременных нажатия не должны создавать дубликаты.
                    await session.rollback()
                    if await session.scalar(select(ChatAgreement).where(
                        ChatAgreement.telegram_id == callback.from_user.id
                    )) is None:
                        raise
        await callback.message.answer(
            "✅ Отлично! Ты подписан на канал и согласен с правилами.",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Не удалось подтвердить подписку и согласие с правилами")
        await callback.message.answer(
            "Сервис временно недоступен, попробуйте позже.", parse_mode="HTML",
        )


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