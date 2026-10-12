"""Обработчик оплаты подписки через Telegram Stars."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from database import update_subscription


router = Router()
logger = logging.getLogger(__name__)


# Цена подписки в звёздах (1 звезда ≈ 1.3-2 ₽ в зависимости от курса)
SUBSCRIPTION_PRICE_STARS = 500
SUBSCRIPTION_DAYS = 30


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription_handler(callback: CallbackQuery) -> None:
    """Отправить счёт на оплату подписки в Stars."""
    if callback.from_user is None or callback.message is None:
        return

    try:
        link = await callback.bot.create_invoice_link(
            title="Подписка на 30 дней",
            description="Безлимитный поиск недвижимости на 30 дней.",
            payload=f"subscription_{callback.from_user.id}_30",
            currency="XTR",
            prices=[LabeledPrice(label="Подписка", amount=SUBSCRIPTION_PRICE_STARS)],
            subscription_period=2592000,
        )
        await callback.message.answer(
            "Нажми кнопку, чтобы оформить подписку:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💎 Оформить подписку", url=link)
            ]]),
        )
        await callback.answer()
    except Exception:
        logger.exception("Не удалось создать ссылку на оплату")
        await callback.answer("Не удалось создать счёт. Попробуй позже.", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
    """Подтвердить готовность принять оплату."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    """Обработать успешную оплату и продлить подписку."""
    if message.from_user is None or message.successful_payment is None:
        return

    payment = message.successful_payment
    try:
        expires_at = await update_subscription(
            telegram_id=message.from_user.id,
            days=SUBSCRIPTION_DAYS,
            payment_id=payment.telegram_payment_charge_id,
            amount_stars=payment.total_amount,
        )
        await message.answer(
            f"✅ Оплата прошла успешно!\n\n"
            f"Подписка активирована до <b>{expires_at.strftime('%d.%m.%Y')}</b>.\n\n"
            f"Теперь можешь искать без ограничений."
        )
        logger.info("Подписка оформлена для %s до %s", message.from_user.id, expires_at)
    except Exception:
        logger.exception("Ошибка при обработке успешной оплаты")
        await message.answer(
            "Оплата получена, но возникла ошибка при активации подписки. "
            "Напишите в поддержку."
        )