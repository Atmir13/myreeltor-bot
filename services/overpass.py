"""Геокодирование адресов и поиск инфраструктуры через OpenStreetMap."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

import aiohttp
from sqlalchemy import select

from database import Property, async_session_factory, get_property_by_id


logger = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MyReeltorBot/1.0 (contact@example.com)"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Рассчитать расстояние между двумя координатами в метрах."""
    radius = 6_371_000
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Получить координаты адреса через Nominatim."""
    if not address.strip():
        logger.warning("Нельзя геокодировать пустой адрес")
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"User-Agent": USER_AGENT}
        params = {"q": address, "format": "json", "limit": 1}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(NOMINATIM_URL, params=params) as response:
                response.raise_for_status()
                data = await response.json()
        if not data:
            logger.warning("Nominatim не нашёл адрес")
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError):
        logger.exception("Ошибка геокодирования адреса")
        return None


async def find_nearby_infrastructure(
    lat: float, lon: float, radius_m: int = 1000
) -> dict[str, list[dict[str, Any]]]:
    """Найти школы и детские сады в заданном радиусе через Overpass."""
    empty: dict[str, list[dict[str, Any]]] = {"schools": [], "kindergartens": []}
    query = f"""[out:json][timeout:25];
(
  node[\"amenity\"=\"school\"](around:{radius_m},{lat},{lon});
  way[\"amenity\"=\"school\"](around:{radius_m},{lat},{lon});
  node[\"amenity\"=\"kindergarten\"](around:{radius_m},{lat},{lon});
  way[\"amenity\"=\"kindergarten\"](around:{radius_m},{lat},{lon});
);
out center;"""
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OVERPASS_URL, data={"data": query}) as response:
                response.raise_for_status()
                payload = await response.json()
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = str(tags.get("name", "")).strip()
            if not name:
                continue
            element_lat = element.get("lat")
            element_lon = element.get("lon")
            center = element.get("center") or {}
            if element_lat is None:
                element_lat = center.get("lat")
            if element_lon is None:
                element_lon = center.get("lon")
            if element_lat is None or element_lon is None:
                continue
            category = "schools" if tags.get("amenity") == "school" else "kindergartens"
            payload_item = {
                "name": name,
                "lat": float(element_lat),
                "lon": float(element_lon),
                "distance_m": round(_haversine(lat, lon, float(element_lat), float(element_lon))),
            }
            empty[category].append(payload_item)
        for category in empty:
            empty[category].sort(key=lambda item: item["distance_m"])
        return empty
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
        logger.exception("Ошибка запроса к Overpass API")
        return empty


async def enrich_property(prop_id: int) -> bool:
    """Обогатить объект инфраструктурой и сохранить JSON в базе."""
    prop = await get_property_by_id(prop_id)
    if prop is None or prop.nearby_infrastructure:
        return False
    if not prop.address:
        logger.warning("У объекта %s отсутствует адрес", prop_id)
        return False
    coordinates = await geocode_address(prop.address)
    if coordinates is None:
        return False
    infrastructure = await find_nearby_infrastructure(*coordinates)
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(Property).where(Property.id == prop_id))
            current = result.scalar_one_or_none()
            if current is None or current.nearby_infrastructure:
                return False
            current.nearby_infrastructure = json.dumps(
                infrastructure, ensure_ascii=False, separators=(",", ":")
            )
            await session.commit()
        logger.info("Инфраструктура сохранена для объекта %s", prop_id)
        return True
    except Exception:
        logger.exception("Не удалось сохранить инфраструктуру для объекта %s", prop_id)
        return False
