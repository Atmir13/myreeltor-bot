"""Админ-панель: управление подписками вручную."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from config import settings
from database import (
    User,
    async_session_factory,
    get_user,
    update_subscription,
    has_active_subscription,
)


router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверить, что пользователь — админ."""
    return user_id == settings.admin_id


@router.message(Command("grant"))
async def grant_handler(message: Message) -> None:
    """Выдать подписку на 30 дней: /grant <telegram_id>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /grant <telegram_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    target = await get_user(target_id)
    if target is None:
        await message.answer(f"Пользователь {target_id} не найден.")
        return

    try:
        expires_at = await update_subscription(
            telegram_id=target_id,
            days=30,
            payment_id="admin_grant",
            amount_stars=0,
        )
        await message.answer(
            f"✅ Подписка выдана пользователю {target_id} до "
            f"{expires_at.strftime('%d.%m.%Y')}."
        )
        logger.info("Админ выдал подписку %s до %s", target_id, expires_at)
    except Exception:
        logger.exception("Ошибка при выдаче подписки")
        await message.answer("Не удалось выдать подписку.")


@router.message(Command("revoke"))
async def revoke_handler(message: Message) -> None:
    """Отозвать подписку: /revoke <telegram_id>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /revoke <telegram_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_id)
        )
        target = result.scalar_one_or_none()
        if target is None:
            await message.answer(f"Пользователь {target_id} не найден.")
            return
        target.subscription_expires_at = None
        await session.commit()

    await message.answer(f"🔒 Подписка пользователя {target_id} отозвана.")


@router.message(Command("stats"))
async def stats_handler(message: Message) -> None:
    """Статистика: всего юзеров, триалов, активных подписок."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    async with async_session_factory() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        trial_used = await session.scalar(
            select(func.count(User.id)).where(User.trial_used == 1)
        )
        subscribed_channel = await session.scalar(
            select(func.count(User.id)).where(User.subscribed_to_channel == 1)
        )
        active_paid = await session.scalar(
            select(func.count(User.id)).where(
                User.subscription_expires_at > datetime.utcnow()
            )
        )

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🎁 Триал использован: {trial_used}\n"
        f"📢 Подписаны на канал: {subscribed_channel}\n"
        f"💎 Активных платных подписок: {active_paid}"
    )


@router.message(Command("check"))
async def check_handler(message: Message) -> None:
    """Статус пользователя: /check <telegram_id>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /check <telegram_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return

    target = await get_user(target_id)
    if target is None:
        await message.answer(f"Пользователь {target_id} не найден.")
        return

    status_lines = [
        f"👤 <b>Пользователь {target_id}</b>",
        f"Username: @{target.username or '—'}",
        f"Триал использован: {'да' if target.trial_used else 'нет'}",
        f"Подписан на канал: {'да' if target.subscribed_to_channel else 'нет'}",
    ]
    if has_active_subscription(target):
        status_lines.append(
            f"💎 Подписка активна до: {target.subscription_expires_at.strftime('%d.%m.%Y')}"
        )
    else:
        status_lines.append("💎 Платной подписки нет")

    await message.answer("\n".join(status_lines))