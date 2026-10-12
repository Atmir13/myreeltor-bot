"""Маршруты сайта-каталога недвижимости."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from database import Property, add_property, async_session_factory, get_property_by_id, search_properties


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
logger = logging.getLogger(__name__)
PAGE_SIZE = 16


def _int_or_none(value: str | int | None, field_name: str = "значение") -> int | None:
    """Преобразовать число из запроса, не допуская ошибки 500."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        logger.warning("Некорректное число в поле %s: %r", field_name, value)
        return None


def _parse_infrastructure(value: str | None) -> dict[str, Any] | None:
    """Безопасно разобрать JSON инфраструктуры для отображения."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Некорректный JSON инфраструктуры")
        return None


def _filters_context(property_type: str | None, rooms: str | None, price_min: int | None,
                    price_max: int | None, district: str | None) -> dict[str, object]:
    """Собрать значения фильтров для повторного отображения формы."""
    return {
        "property_type": property_type or "all",
        "rooms": rooms or "all",
        "price_min": price_min,
        "price_max": price_max,
        "district": district or "all",
    }


async def _properties_by_ids(ids: list[int]) -> list[Property]:
    """Получить избранные объекты в безопасном порядке."""
    if not ids:
        return []
    async with async_session_factory() as session:
        result = await session.execute(select(Property).where(Property.id.in_(ids)))
        found = {prop.id: prop for prop in result.scalars().all()}
    return [found[prop_id] for prop_id in ids if prop_id in found]


@router.get("/")
async def index(
    request: Request,
    property_type: str | None = None,
    rooms: str | None = None,
    price_min: str | None = None,
    price_max: str | None = None,
    district: str | None = None,
    page: str | None = None,
):
    """Показать каталог с фильтрами и постраничной навигацией."""
    normalized_type = property_type.strip() if property_type and property_type.strip() not in {"all", ""} else None
    normalized_rooms = None
    if rooms and rooms.strip() not in {"all", ""}:
        normalized_rooms = _int_or_none(rooms, "комнаты")
    min_price = _int_or_none(price_min, "цена от")
    max_price = _int_or_none(price_max, "цена до")
    current_page = max(1, _int_or_none(page, "страница") or 1)
    clean_district = district.strip() if district and district.strip() not in {"all", ""} else None
    logger.info(
        "Поиск: district=%r, type=%r, rooms=%r, price=%r-%r",
        district,
        property_type,
        rooms,
        price_min,
        price_max,
    )

    try:
        all_properties = await search_properties(
            property_type=normalized_type,
            rooms=normalized_rooms,
            price_min=min_price,
            price_max=max_price,
            district=clean_district,
            limit=None,
        )
        start = (current_page - 1) * PAGE_SIZE
        properties = all_properties[start:start + PAGE_SIZE]
        total_pages = max(1, (len(all_properties) + PAGE_SIZE - 1) // PAGE_SIZE)
        if current_page > total_pages:
            current_page = total_pages
            start = (current_page - 1) * PAGE_SIZE
            properties = all_properties[start:start + PAGE_SIZE]
    except Exception:
        logger.exception("Ошибка поиска объектов с фильтрами")
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"properties": [], "error": "Не удалось выполнить поиск. Попробуйте изменить параметры.",
                     "page": 1, "total_pages": 1, "filters": _filters_context(property_type, rooms, min_price, max_price, district)},
            status_code=200,
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"properties": properties, "page": current_page, "total_pages": total_pages,
                 "filters": _filters_context(property_type, rooms, min_price, max_price, district)},
    )


@router.get("/favorites")
async def favorites(request: Request, ids: str | None = None):
    """Показать объекты, сохранённые в localStorage браузера."""
    parsed_ids: list[int] = []
    for raw_id in (ids or "").split(","):
        value = _int_or_none(raw_id, "избранное")
        if value is not None:
            parsed_ids.append(value)
    try:
        properties = await _properties_by_ids(parsed_ids)
    except Exception:
        logger.exception("Ошибка загрузки избранных объектов")
        properties = []
    return templates.TemplateResponse(request=request, name="favorites.html", context={"properties": properties})


@router.get("/property/{property_id}")
async def property_detail(request: Request, property_id: int):
    """Показать карточку одного объекта."""
    prop = await get_property_by_id(property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return templates.TemplateResponse(request=request, name="property.html",
                                      context={"property": prop, "infrastructure": _parse_infrastructure(prop.nearby_infrastructure)})


@router.get("/add")
async def add_property_form(request: Request):
    """Показать форму добавления объекта."""
    return templates.TemplateResponse(request=request, name="add_property.html", context={})


@router.post("/add")
async def add_property_submit(request: Request):
    """Добавить объект из формы и открыть его карточку."""
    try:
        form = await request.form()
        value = lambda name: str(form.get(name, "")).strip()
        title = value("title")
        if not title:
            raise HTTPException(status_code=400, detail="Название обязательно")
        seller_phone = value("seller_phone")
        seller_telegram = value("seller_telegram")
        property_id = await add_property(
            title=title, price=_int_or_none(value("price"), "цена"), address=value("address") or None,
            district=value("district") or None, property_type=value("property_type") or None,
            rooms=_int_or_none(value("rooms"), "комнаты"), area=_int_or_none(value("area"), "площадь"),
            floor=_int_or_none(value("floor"), "этаж"), floors_total=_int_or_none(value("floors_total"), "этажей в доме"),
            description=value("description") or None,
            seller_telegram=seller_phone or seller_telegram or None,
        )
        return RedirectResponse(url=f"/property/{property_id}", status_code=303)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Ошибка добавления объекта через сайт")
        raise HTTPException(status_code=400, detail="Не удалось добавить объект. Проверьте заполненные поля.")
