"""Админ-панель: управление подписками вручную."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from config import settings
from database import (
    User,
    add_property,
    async_session_factory,
    get_property_by_id,
    get_user,
    has_active_subscription,
    mark_property_sold,
    update_subscription,
)
from services.overpass import enrich_property


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


@router.message(Command("sold"))
async def sold_handler(message: Message) -> None:
    """Пометить объект проданным: /sold <id>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /sold <id>")
        return
    try:
        property_id = int(parts[1])
    except ValueError:
        await message.answer("ID объекта должен быть числом.")
        return
    try:
        changed = await mark_property_sold(property_id)
        await message.answer(
            "✅ Объект помечен как проданный." if changed else "Объект с таким ID не найден."
        )
    except Exception:
        logger.exception("Ошибка при пометке объекта проданным")
        await message.answer("Не удалось обновить объект.")


@router.message(Command("add_property"))
async def add_property_handler(message: Message) -> None:
    """Добавить тестовый объект через разделитель |."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    raw = (message.text or "").partition(" ")[2].strip()
    parts = [part.strip() for part in raw.split("|")]
    if not 7 <= len(parts) <= 9:
        await message.answer(
            "Нужно минимум 7 параметров, разделённых <b>|</b>:\n"
            "<code>Название | цена | комнаты | площадь | адрес | район | тип | "
            "[source_url] | [seller_telegram]</code>\n\n"
            "Пример:\n"
            "<code>/add_property Двушка на Ленина | 8200000 | 2 | 54 | "
            "ул. Ленина, 15 | Центральный | квартира | "
            "https://www.avito.ru/test | reeltor_ivan</code>",
            parse_mode="HTML",
        )
        return
    try:
        title = parts[0]
        price_str = parts[1]
        rooms_str = parts[2]
        area_str = parts[3]
        address = parts[4]
        district = parts[5]
        property_type = parts[6]
        source_url = parts[7] if len(parts) > 7 and parts[7] else None
        seller_telegram = (
            parts[8].lstrip("@") if len(parts) > 8 and parts[8] else None
        )
        price = int(price_str)
        rooms = int(rooms_str)
        area = int(area_str)
        property_id = await add_property(
            title=title[:500],
            price=price,
            rooms=rooms,
            area=area,
            address=address[:500],
            district=district[:255],
            property_type=property_type[:50],
            source_url=source_url[:1000] if source_url else None,
            seller_telegram=seller_telegram[:255] if seller_telegram else None,
        )
        response_lines = [
            "✅ Объект добавлен",
            f"ID: {property_id}",
            f"Название: {title}",
            f"Цена: {price:,} ₽".replace(",", " "),
            f"Комнат: {rooms}",
            f"Площадь: {area} м²",
            f"Адрес: {address}",
            f"Район: {district}",
            f"Тип: {property_type}",
        ]
        if source_url:
            response_lines.append(f"🔗 Объявление: {source_url}")
        if seller_telegram:
            response_lines.append(f"💬 Продавец: @{seller_telegram}")
        await message.answer("\n".join(response_lines))
        asyncio.create_task(
            _enrich_and_notify(property_id, message.bot, message.from_user.id)
        )
    except ValueError:
        await message.answer("Цена, комнаты и площадь должны быть числами.")
    except Exception:
        logger.exception("Ошибка при добавлении тестового объекта")
        await message.answer("Не удалось добавить объект.")


async def _enrich_and_notify(prop_id: int, bot, admin_id: int) -> None:
    """Обогатить объект инфраструктурой и уведомить администратора."""
    try:
        success = await enrich_property(prop_id)
        if success:
            prop = await get_property_by_id(prop_id)
            if prop and prop.nearby_infrastructure:
                data = json.loads(prop.nearby_infrastructure)
                schools = len(data.get("schools", []))
                kindergartens = len(data.get("kindergartens", []))
                await bot.send_message(
                    admin_id,
                    f"🎓 Инфраструктура для объекта #{prop_id} загружена: "
                    f"{schools} школ, {kindergartens} садиков.",
                )
                return
        logger.warning("Инфраструктура для объекта %s не загружена", prop_id)
        await bot.send_message(
            admin_id,
            f"⚠️ Не удалось загрузить инфраструктуру для объекта #{prop_id}. "
            "Возможно, адрес не найден или Overpass недоступен.",
        )
    except Exception:
        logger.exception("Ошибка при обогащении объекта #%s", prop_id)
        try:
            await bot.send_message(
                admin_id,
                f"❌ Ошибка при загрузке инфраструктуры для объекта #{prop_id}.",
            )
        except Exception:
            logger.exception("Не удалось уведомить администратора об ошибке обогащения")


@router.message(Command("enrich"))
async def enrich_handler(message: Message) -> None:
    """Загрузить инфраструктуру для объекта: /enrich <id>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /enrich <id>")
        return
    try:
        property_id = int(parts[1])
        enriched = await enrich_property(property_id)
        if not enriched:
            await message.answer("Не удалось (адрес не найден или данные уже есть)")
            return
        from database import get_property_by_id

        prop = await get_property_by_id(property_id)
        data = json.loads(prop.nearby_infrastructure or "{}") if prop else {}
        await message.answer(
            f"✅ Инфраструктура добавлена для объекта #{property_id}\n"
            f"Школ: {len(data.get('schools', []))}\n"
            f"Садиков: {len(data.get('kindergartens', []))}"
        )
    except ValueError:
        await message.answer("ID объекта должен быть числом.")
    except Exception:
        logger.exception("Ошибка обогащения объекта")
        await message.answer("Не удалось загрузить инфраструктуру.")


@router.message(Command("reset_trial"))
async def reset_trial_handler(message: Message) -> None:
    """Сбросить триал текущего администратора для тестирования."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    try:
        user = await get_user(message.from_user.id)
        if user is None:
            await message.answer("Пользователь ещё не зарегистрирован.")
            return
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user.id))
            current_user = result.scalar_one_or_none()
            if current_user is None:
                await message.answer("Пользователь не найден.")
                return
            current_user.trial_used = 0
            await session.commit()
        await message.answer("✅ Триал сброшен")
        logger.info("Администратор сбросил свой триал")
    except Exception:
        logger.exception("Ошибка при сбросе триала")
        await message.answer("Не удалось сбросить триал.")


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