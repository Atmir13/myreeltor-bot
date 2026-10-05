"""Формирование ссылок на карту OpenStreetMap."""

from __future__ import annotations

from typing import Any


async def generate_osm_link(lat: float, lon: float, zoom: int = 16) -> str:
    """Сформировать ссылку OpenStreetMap с отмеченной точкой."""
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"


async def generate_map_links(prop: Any) -> dict[str, str | None]:
    """Вернуть ссылку на OSM, если у объекта есть обе координаты."""
    if prop.latitude is None or prop.longitude is None:
        return {"osm": None}
    return {"osm": await generate_osm_link(prop.latitude, prop.longitude)}
