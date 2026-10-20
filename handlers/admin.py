"""Админ-панель: управление подписками вручную."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from config import settings
from database import (
    User,
    Property,
    UserListing,
    PendingGrant,
    get_user_by_username,
    add_property,
    async_session_factory,
    get_property_by_id,
    update_property_coords,
    get_user,
    has_active_subscription,
    mark_property_sold,
    update_subscription,
)
from services.overpass import enrich_property
from services.moderation import publish_listing


router = Router()
logger = logging.getLogger(__name__)


class ImportCSVStates(StatesGroup):
    """Состояние ожидания CSV-файла от администратора."""

    waiting_for_file = State()


def is_admin(user_id: int) -> bool:
    """Проверить, что пользователь — админ."""
    return user_id == settings.admin_id


@router.callback_query(F.data.startswith("approve_"))
async def approve_listing(callback: CallbackQuery) -> None:
    """Одобрить заявку и опубликовать её."""
    if callback.from_user is None or not is_admin(callback.from_user.id):
        return
    listing_id = int(callback.data.split("_", 1)[1])
    await publish_listing(listing_id, callback.bot)
    await callback.answer(f"Заявление #{listing_id} одобрено")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("reject_"))
async def reject_listing(callback: CallbackQuery) -> None:
    """Отклонить заявку."""
    if callback.from_user is None or not is_admin(callback.from_user.id):
        return
    listing_id = int(callback.data.split("_", 1)[1])
    async with async_session_factory() as session:
        listing = await session.get(UserListing, listing_id)
        if listing:
            listing.status = "rejected"
            await session.commit()
    await callback.answer(f"Объявление #{listing_id} отклонено")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.message(Command("pending"))
async def pending_handler(message: Message) -> None:
    """Показать заявки, ожидающие модерации."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    async with async_session_factory() as session:
        result = await session.execute(select(UserListing).where(UserListing.status == "pending_review"))
        listings = result.scalars().all()
    if not listings:
        await message.answer("Заявок на проверку нет.")
        return
    for listing in listings:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{listing.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{listing.id}"),
        ]])
        await message.answer(f"<b>Заявка #{listing.id}</b>\n{listing.title or 'Поиск'}\nКонтакт: {listing.contact or '—'}", parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("moderation"))
async def moderation_handler(message: Message) -> None:
    """Показать опубликованные за последние 30 дней заявки."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    async with async_session_factory() as session:
        result = await session.execute(select(UserListing).where(UserListing.status == "approved", UserListing.created_at >= datetime.utcnow() - __import__("datetime").timedelta(days=30)))
        listings = result.scalars().all()
    for listing in listings:
        await message.answer(f"#{listing.id} {listing.title or 'Без названия'}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{listing.id}")]]))
    if not listings:
        await message.answer("Опубликованных объявлений за 30 дней нет.")


@router.callback_query(F.data.startswith("delete_"))
async def delete_listing(callback: CallbackQuery) -> None:
    """Удалить опубликованную заявку из канала."""
    if callback.from_user is None or not is_admin(callback.from_user.id):
        return
    listing_id = int(callback.data.split("_", 1)[1])
    async with async_session_factory() as session:
        listing = await session.get(UserListing, listing_id)
        if listing and listing.message_id:
            await callback.bot.delete_message(settings.channel_id, listing.message_id)
        if listing:
            listing.status = "deleted"
            await session.commit()
    await callback.answer("Удалено")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.message(Command("grant"))
async def grant_handler(message: Message) -> None:
    """Выдать подписку по @username или создать ссылку-приглашение."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /grant <telegram_id>")
        return

    username = parts[1].lstrip("@")
    target = await get_user_by_username(username)
    if target is None:
        token = secrets.token_urlsafe(24)
        async with async_session_factory() as session:
            session.add(PendingGrant(token=token, username=username))
            await session.commit()
        await message.answer(f"Пользователь @{username} не найден.\nОтправьте ему эту ссылку:\nhttps://t.me/MyReeltor_bot?start=grant_{token}")
        return

    try:
        expires_at = await update_subscription(
            telegram_id=target.telegram_id,
            days=30,
            payment_id="admin_grant",
            amount_stars=0,
        )
        await message.answer(
            f"✅ Подписка выдана @{username} до "
            f"{expires_at.strftime('%d.%m.%Y')}."
        )
        logger.info("Админ выдал подписку @%s до %s", username, expires_at)
    except Exception:
        logger.exception("Ошибка при выдаче подписки")
        await message.answer("Не удалось выдать подписку.")


@router.message(Command("revoke"))
async def revoke_handler(message: Message) -> None:
    """Отозвать подписку по @username."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /revoke <telegram_id>")
        return

    username = parts[1].lstrip("@")
    target = await get_user_by_username(username)
    if target is None:
        await message.answer(f"Пользователь @{username} не найден.")
        return
    target_id = target.telegram_id

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

    await message.answer(f"🔒 Подписка пользователя @{username} отозвана.")


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


@router.message(Command("coords"))
async def coords_handler(message: Message) -> None:
    """Сохранить координаты объекта: /coords <id> <lat> <lon>."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("Использование: /coords <id> <lat> <lon>")
        return
    try:
        property_id = int(parts[1])
        lat = float(parts[2])
        lon = float(parts[3])
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError
        saved = await update_property_coords(property_id, lat, lon)
        if not saved:
            await message.answer(f"Объект #{property_id} не найден.")
            return
        await message.answer(
            f"✅ Координаты для объекта #{property_id} сохранены: {lat}, {lon}"
        )
    except ValueError:
        await message.answer("ID, широта и долгота должны быть корректными числами.")
    except Exception:
        logger.exception("Ошибка сохранения координат объекта")
        await message.answer("Не удалось сохранить координаты.")


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
    """Показать статус пользователя по @username."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /check <telegram_id>")
        return

    username = parts[1].lstrip("@")
    target = await get_user_by_username(username)
    if target is None:
        await message.answer(f"Пользователь @{username} не найден.")
        return

    status_lines = [
        f"👤 <b>Пользователь @{username}</b>",
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


@router.message(Command("subscribers"))
async def subscribers_handler(message: Message) -> None:
    """Показать пользователей и состояние их подписок."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        users = list(result.scalars().all())
    now = datetime.utcnow()
    users.sort(key=lambda user: (not has_active_subscription(user), user.username or ""))
    for start in range(0, len(users), 20):
        lines = []
        for user in users[start:start + 20]:
            name = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
            if has_active_subscription(user):
                line = f"✅ {name} — подписка до {user.subscription_expires_at:%d.%m.%Y}"
            elif user.subscription_expires_at:
                line = f"❌ {name} — подписка истекла {user.subscription_expires_at:%d.%m.%Y}"
            else:
                line = f"⚪ {name} — нет подписки"
            lines.append(line)
        keyboard = []
        if start >= 20:
            keyboard.append(InlineKeyboardButton(text="← Назад", callback_data=f"subs_page:{start - 20}"))
        if start + 20 < len(users):
            keyboard.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"subs_page:{start + 20}"))
        await message.answer("<b>Подписчики</b>\n" + "\n".join(lines), parse_mode="HTML",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[keyboard]) if keyboard else None)


@router.callback_query(F.data.startswith("subs_page:"))
async def subscribers_page(callback: CallbackQuery) -> None:
    """Показать страницу списка подписчиков."""
    if callback.from_user is None or not is_admin(callback.from_user.id):
        return
    offset = int(callback.data.split(":", 1)[1])
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        users = list(result.scalars().all())
    users.sort(key=lambda user: (not has_active_subscription(user), user.username or ""))
    page = users[offset:offset + 20]
    lines = []
    for user in page:
        name = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
        if has_active_subscription(user):
            lines.append(f"✅ {name} — подписка до {user.subscription_expires_at:%d.%m.%Y}")
        elif user.subscription_expires_at:
            lines.append(f"❌ {name} — подписка истекла {user.subscription_expires_at:%d.%m.%Y}")
        else:
            lines.append(f"⚪ {name} — нет подписки")
    buttons = []
    if offset:
        buttons.append(InlineKeyboardButton(text="← Назад", callback_data=f"subs_page:{max(0, offset - 20)}"))
    if offset + 20 < len(users):
        buttons.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"subs_page:{offset + 20}"))
    await callback.message.edit_text("<b>Подписчики</b>\n" + "\n".join(lines), parse_mode="HTML",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None)
    await callback.answer()


@router.message(Command("import_csv"))
async def import_csv_start(message: Message, state: FSMContext) -> None:
    """Запросить CSV-файл для импорта."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await state.set_state(ImportCSVStates.waiting_for_file)
    await message.answer("📎 Отправьте CSV-файл (экспорт ads-api.ru).\nИли /cancel чтобы отменить.")


@router.message(ImportCSVStates.waiting_for_file, F.document)
async def import_csv_file(message: Message, state: FSMContext) -> None:
    """Скачать и импортировать CSV-файл администратора."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    if message.document is None:
        await message.answer("❌ Это не файл. Отправьте CSV.")
        return
    tmp_path = f"/tmp/import_{message.document.file_id}.csv"
    try:
        file = await message.bot.get_file(message.document.file_id)
        await message.bot.download_file(file.file_path, tmp_path)
        from scripts.import_csv import import_csv as do_import
        result = await do_import(tmp_path)
        await message.answer(f"✅ Импорт завершён.\nВсего строк: {result['total']}\nИмпортировано: {result['imported']}\nПропущено: {result['skipped']}")
    except Exception:
        logger.exception("Ошибка импорта CSV")
        await message.answer("❌ Ошибка импорта. Смотри логи.")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        await state.clear()


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """Отменить текущее состояние администратора."""
    if await state.get_state() is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(Command("sync_ads"))
async def sync_ads_handler(message: Message) -> None:
    """Запустить ручную синхронизацию ads-api."""
    if message.from_user is None or not is_admin(message.from_user.id):
        return
    await message.answer("⏳ Синхронизация запущена...")
    try:
        from services.ads_api import sync_ads
        result = await sync_ads()
        await message.answer(f"✅ Синхронизация завершена.\nПолучено: {result['fetched']}\nСохранено: {result['saved']}")
    except Exception:
        logger.exception("Ошибка синхронизации ads")
        await message.answer("❌ Ошибка. Смотри логи.")