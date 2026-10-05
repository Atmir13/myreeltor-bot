"""Обработчик поиска недвижимости по текстовому запросу."""

from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import (
    Property,
    async_session_factory,
    get_or_create_user,
    search_properties,
    update_trial_used,
)
from services.access import (
    LEVEL_BLOCKED,
    LEVEL_CHANNEL,
    LEVEL_PAID,
    LEVEL_TRIAL,
    get_access_level,
    get_limit_for_level,
)
from services.parser import SearchQuery, parse_query


router = Router()
logger = logging.getLogger(__name__)


SEARCH_HELP = (
    "Опиши подробнее, что ищешь. Например:\n"
    "— двушка до 15 млн\n"
    "— дом 4 комнаты до 20 млн\n"
    "— студия район Центральный"
)


def paywall_keyboard() -> InlineKeyboardMarkup:
    """Сформировать кнопку перехода к оплате."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Оформить подписку", callback_data="buy_subscription")]
        ]
    )


def similar_keyboard() -> InlineKeyboardMarkup:
    """Сформировать кнопку повторного поиска похожего объекта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти похожие", callback_data="find_similar")]
        ]
    )


def property_keyboard(prop: Property) -> InlineKeyboardMarkup | None:
    """Сформировать кнопку контакта с продавцом или источником."""
    url: str | None = None
    label: str | None = None
    if prop.source_url:
        url = prop.source_url
        label = "🔗 Открыть объявление"
    elif prop.seller_telegram:
        username = prop.seller_telegram.lstrip("@").strip()
        if username:
            url = f"https://t.me/{username}"
            label = "💬 Написать продавцу"
    if not url or not label:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def _value(value: object | None, fallback: str = "—") -> str:
    """Безопасно преобразовать значение в HTML-текст."""
    return html.escape(str(value)) if value is not None else fallback


def format_property(prop: Property) -> str:
    """Собрать HTML-карточку объекта."""
    lines: list[str] = []
    if prop.status == "sold":
        lines.append("😔 <b>К сожалению, этот объект уже продан.</b>")
    elif prop.status == "archived":
        lines.append("⏸️ <b>Это объявление снято с публикации.</b>")

    lines.append(f"🏠 <b>{_value(prop.title)}</b>")
    if prop.price is not None:
        lines.append(f"💰 {_value(f'{prop.price:,}'.replace(',', ' '))} ₽")
    if prop.address:
        lines.append(f"📍 {_value(prop.address)}")
    if prop.rooms is not None:
        lines.append(f"🚪 Комнат: {_value(prop.rooms)}")
    if prop.area is not None:
        lines.append(f"📐 Площадь: {_value(prop.area)} м²")
    if prop.floor is not None or prop.floors_total is not None:
        floor = _value(prop.floor)
        floors_total = _value(prop.floors_total)
        lines.append(f"🏢 Этаж: {floor} / {floors_total}")
    if prop.description:
        lines.append(f"\n{html.escape(prop.description[:300])}")
    return "\n".join(lines)


async def fetch_properties(query: SearchQuery, limit: int | None) -> list[Property]:
    """Найти активные объекты по распарсенным фильтрам."""
    return await search_properties(
        property_type=query.property_type,
        rooms=query.rooms,
        price_max=query.price_max,
        price_min=query.price_min,
        district=query.district,
        area_min=query.area_min,
        area_max=query.area_max,
        limit=limit,
    )


@router.callback_query(lambda callback: callback.data == "find_similar")
async def find_similar_handler(callback: CallbackQuery) -> None:
    """Ответить на кнопку похожих объектов без полноценного поиска."""
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Уточни параметры — и я найду похожие.")


@router.message(lambda msg: msg.text is not None and not msg.text.startswith("/"))
async def search_handler(message: Message) -> None:
    """Обработать пользовательский запрос и показать найденные карточки."""
    if message.from_user is None or message.text is None:
        return

    try:
        user = await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        level = await get_access_level(message.bot, user)
        logger.info("Получен поисковый запрос, уровень доступа: %s", level)

        if level == LEVEL_BLOCKED:
            await message.answer(
                "🔒 Бесплатный запрос использован.\n\n"
                "Оформи подписку — и ищи без ограничений на 30 дней.",
                reply_markup=paywall_keyboard(),
            )
            return

        query = parse_query(message.text[:500])
        if query.is_empty() or not query.has_main_filters():
            await message.answer(SEARCH_HELP)
            return

        properties = await fetch_properties(query, get_limit_for_level(level))
        if not properties:
            if level in (LEVEL_TRIAL, LEVEL_CHANNEL):
                await update_trial_used(message.from_user.id)
            await message.answer(
                "По твоему запросу ничего не найдено. Попробуй другие параметры "
                "или оформи подписку.",
                reply_markup=paywall_keyboard(),
            )
            return

        for prop in properties:
            markup = similar_keyboard() if prop.status in {"sold", "archived"} else property_keyboard(prop)
            await message.answer(format_property(prop), parse_mode="HTML", reply_markup=markup)

        if level in (LEVEL_TRIAL, LEVEL_CHANNEL):
            await update_trial_used(message.from_user.id)
            await message.answer(
                f"🎁 Это был твой бесплатный запрос ({len(properties)} объектов).\n\n"
                "Чтобы искать без ограничений — оформи подписку.",
                reply_markup=paywall_keyboard(),
            )
        elif level == LEVEL_PAID:
            await message.answer(f"Найдено объектов: {len(properties)}. Подписка активна.")
    except Exception:
        logger.exception("Ошибка при обработке поискового запроса")
        await message.answer("Сервис временно недоступен, попробуйте позже.")
