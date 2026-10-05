"""Обработчик поиска недвижимости по текстовому запросу."""

from __future__ import annotations

import html
import json
import logging

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import (
    Property,
    async_session_factory,
    get_or_create_user,
    get_property_by_id,
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
from services.map_generator import generate_osm_link
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


async def build_property_keyboard(prop: Property) -> InlineKeyboardMarkup | None:
    """Собрать клавиатуру карточки отдельными рядами."""
    rows: list[list[InlineKeyboardButton]] = []
    if prop.source_url:
        rows.append([InlineKeyboardButton(text="🔗 Открыть объявление", url=prop.source_url)])
    elif prop.seller_telegram:
        username = prop.seller_telegram.lstrip("@").strip()
        if username:
            rows.append(
                [InlineKeyboardButton(text="💬 Написать продавцу", url=f"https://t.me/{username}")]
            )
    if prop.latitude is not None and prop.longitude is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗺️ Показать на карте",
                    url=await generate_osm_link(prop.latitude, prop.longitude),
                )
            ]
        )
    if prop.nearby_infrastructure:
        try:
            data = json.loads(prop.nearby_infrastructure)
            total = len(data.get("schools", [])) + len(data.get("kindergartens", []))
            if total > 1:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text="📍 Показать все", callback_data=f"infra:{prop.id}"
                        )
                    ]
                )
        except (TypeError, ValueError):
            logger.warning("Некорректный JSON инфраструктуры для объекта %s", prop.id)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def infrastructure_keyboard(prop: Property) -> InlineKeyboardMarkup | None:
    """Сформировать кнопку полного списка инфраструктуры."""
    if not prop.nearby_infrastructure:
        return None
    try:
        data = json.loads(prop.nearby_infrastructure)
    except (TypeError, ValueError):
        logger.warning("Некорректный JSON инфраструктуры для объекта %s", prop.id)
        return None
    total = len(data.get("schools", [])) + len(data.get("kindergartens", []))
    if total <= 1:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Показать все", callback_data=f"infra:{prop.id}")]
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
    if prop.nearby_infrastructure:
        try:
            infrastructure = json.loads(prop.nearby_infrastructure)
            schools = infrastructure.get("schools", [])
            kindergartens = infrastructure.get("kindergartens", [])
            nearby_lines = ["🎓 Рядом:"]
            if schools:
                school = schools[0]
                nearby_lines.append(
                    f"• {_value(school.get('name'))} — {_value(school.get('distance_m'))} м"
                )
            if kindergartens:
                kindergarten = kindergartens[0]
                nearby_lines.append(
                    f"• {_value(kindergarten.get('name'))} — "
                    f"{_value(kindergarten.get('distance_m'))} м"
                )
            if len(nearby_lines) > 1:
                lines.extend(nearby_lines)
        except (TypeError, ValueError):
            logger.warning("Некорректный JSON инфраструктуры для объекта %s", prop.id)
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
        text_query=query.text_query,
        limit=limit,
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("infra:"))
async def infrastructure_handler(callback: CallbackQuery) -> None:
    """Показать полный список школ и садиков для объекта."""
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        property_id = int(callback.data.split(":", 1)[1])
        prop = await get_property_by_id(property_id)
        if prop is None or not prop.nearby_infrastructure:
            await callback.message.answer("Данные об инфраструктуре пока недоступны.")
            return
        data = json.loads(prop.nearby_infrastructure)
        lines = ["🎓 Школы рядом:"]
        schools = data.get("schools", [])
        lines.extend(
            f"• {_value(item.get('name'))} — {_value(item.get('distance_m'))} м"
            for item in schools
        )
        lines.append("\n🧸 Садики рядом:")
        kindergartens = data.get("kindergartens", [])
        lines.extend(
            f"• {_value(item.get('name'))} — {_value(item.get('distance_m'))} м"
            for item in kindergartens
        )
        await callback.message.answer("\n".join(lines))
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.exception("Некорректные данные инфраструктуры")
        await callback.message.answer("Не удалось показать инфраструктуру.")
    except Exception:
        logger.exception("Ошибка показа инфраструктуры")
        await callback.message.answer("Сервис временно недоступен, попробуйте позже.")


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
            rows: list[list[InlineKeyboardButton]] = []
            if prop.status in {"sold", "archived"}:
                rows.extend(similar_keyboard().inline_keyboard)
            card_markup = await build_property_keyboard(prop)
            if card_markup:
                rows.extend(card_markup.inline_keyboard)
            markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
            await message.answer(
                format_property(prop), parse_mode="HTML", reply_markup=markup
            )

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
