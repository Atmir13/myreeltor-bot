"""Маршруты сайта-каталога недвижимости."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from database import add_property, get_property_by_id, search_properties

from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _int_or_none(value: str | None) -> int | None:
    """Преобразовать форму с целым числом или вернуть None."""
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_infrastructure(value: str | None) -> dict[str, Any] | None:
    """Безопасно разобрать JSON инфраструктуры для отображения."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


@router.get("/")
async def index(
    request: Request,
    property_type: str | None = None,
    rooms: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    district: str | None = None,
):
    """Показать каталог с фильтрами."""
    normalized_type = property_type if property_type and property_type != "all" else None
    normalized_rooms = None
    if rooms and rooms != "all":
        normalized_rooms = 4 if rooms == "4+" else _int_or_none(rooms)

    properties = await search_properties(
        property_type=normalized_type,
        rooms=normalized_rooms,
        price_min=price_min,
        price_max=price_max,
        district=district.strip() if district else None,
        limit=20,
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "properties": properties,
            "filters": {
                "property_type": property_type or "all",
                "rooms": rooms or "all",
                "price_min": price_min,
                "price_max": price_max,
                "district": district or "",
            },
        },
    )


@router.get("/property/{property_id}")
async def property_detail(request: Request, property_id: int):
    """Показать карточку одного объекта."""
    prop = await get_property_by_id(property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return templates.TemplateResponse(
        request=request,
        name="property.html",
        context={"property": prop, "infrastructure": _parse_infrastructure(prop.nearby_infrastructure)},
    )


@router.get("/add")
async def add_property_form(request: Request):
    """Показать форму добавления объекта."""
    return templates.TemplateResponse(request=request, name="add_property.html", context={})


@router.post("/add")
async def add_property_submit(request: Request):
    """Добавить объект из form-urlencoded-формы и открыть его карточку."""
    form = await request.form()
    title = str(form.get("title", ""))
    if not title.strip():
        raise HTTPException(status_code=400, detail="Название обязательно")
    def value(name: str) -> str:
        return str(form.get(name, "")).strip()

    property_id = await add_property(
        title=title.strip(),
        price=_int_or_none(value("price")),
        address=value("address") or None,
        district=value("district") or None,
        property_type=value("property_type") or None,
        rooms=_int_or_none(value("rooms")),
        area=_int_or_none(value("area")),
        floor=_int_or_none(value("floor")),
        floors_total=_int_or_none(value("floors_total")),
        description=value("description") or None,
        seller_telegram=value("seller_telegram") or None,
    )
    return RedirectResponse(url=f"/property/{property_id}", status_code=303)
