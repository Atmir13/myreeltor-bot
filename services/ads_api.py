"""Синхронизация объявлений с ads-api.ru."""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
from sqlalchemy import select

from database import Property, add_property, async_session_factory


logger = logging.getLogger(__name__)
ADS_API_URL = "https://ads-api.ru/main/api"


def _int_or_none(value: object) -> int | None:
    """Безопасно преобразовать значение в целое число."""
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(" ", "").replace(",", "."))) or None
    except (TypeError, ValueError):
        return None


async def fetch_ads(city: str = "Нальчик", limit: int = 50) -> list[dict]:
    """Получить объявления из ads-api.ru."""
    params = {
        "user": os.getenv("ADS_API_USER", ""),
        "token": os.getenv("ADS_API_TOKEN", ""),
        "city": city,
        "category_id": 1,
        "limit": limit,
        "page": 1,
    }
    proxy = os.getenv("PROXY_URL")
    if proxy:
        logger.info("Используется прокси: %s", proxy.split("@")[-1])

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(ADS_API_URL, params=params, proxy=proxy, timeout=timeout) as response:
                if response.status == 401:
                    logger.error("Неверный логин/токен ads-api.ru")
                    return []
                if response.status == 403:
                    logger.error("IP заблокирован (проверьте прокси)")
                    return []
                response.raise_for_status()
                payload = await response.json(content_type=None)
        if isinstance(payload, list):
            ads = payload
        elif isinstance(payload, dict):
            ads = payload.get("ads") or payload.get("data") or payload.get("items") or []
        else:
            ads = []
        result = [ad for ad in ads if isinstance(ad, dict)]
        logger.info("Получено %d объявлений", len(result))
        return result
    except asyncio.TimeoutError:
        logger.error("Таймаут при запросе")
        return []
    except aiohttp.ClientError as error:
        logger.error("Ошибка соединения: %s", error)
        return []
    except Exception:
        logger.exception("Ошибка получения объявлений ads-api.ru")
        return []


async def _source_exists(source_url: str) -> bool:
    """Проверить дубликат по URL источника."""
    async with async_session_factory() as session:
        result = await session.execute(select(Property.id).where(Property.source_url == source_url).limit(1))
        return result.scalar_one_or_none() is not None


async def save_ads(ads: list[dict]) -> int:
    """Сохранить новые объявления и вернуть их количество."""
    saved = 0
    for ad in ads:
        try:
            source_url = str(ad.get("url") or ad.get("source_url") or "").strip()
            if not source_url or await _source_exists(source_url):
                continue
            title = str(ad.get("title") or "Объявление").strip()
            property_id = await add_property(
                title=title,
                price=_int_or_none(ad.get("price")),
                address=ad.get("address"),
                district=ad.get("city"),
                property_type=ad.get("category", "квартира"),
                rooms=_int_or_none(ad.get("rooms")),
                area=_int_or_none(ad.get("area")),
                description=ad.get("description", ""),
                photo_url=ad.get("photo_url"),
                source="ads_api",
                source_url=source_url,
            )
            saved += 1
            logger.info("Сохранено объявление #%s", property_id)
        except Exception:
            logger.exception("Ошибка сохранения объявления ads-api")
    return saved


async def sync_ads(city: str = "Нальчик") -> dict[str, int]:
    """Получить и сохранить объявления выбранного города."""
    ads = await fetch_ads(city=city)
    saved = await save_ads(ads)
    return {"fetched": len(ads), "saved": saved}
